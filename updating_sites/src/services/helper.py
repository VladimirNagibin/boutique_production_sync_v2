from typing import Any


def get_request_for_upd(portal: str) -> Any:
    if portal == "ornam":
        return """
            TRUNCATE TABLE `EXCategories`;
            INSERT INTO `EXCategories` ( `category_id`, `parent_id`, `name`, `top`, `columns`, `sort_order`, `image_name`, `date_added`, `date_modified`, `language_id`, `seo_keyword`, `description`, `meta_description`, `meta_keywords`, `seo_title`, `seo_h1`, `store_ids`, `layout`)
            SELECT `Categories`.`category_id`, `Categories`.`parent_id`, `Categories`.`name`, `Categories`.`top`, `Categories`.`columns`, `Categories`.`sort_order`, `Categories`.`image_name`, `Categories`.`date_added`, `Categories`.`date_modified`, `Categories`.`language_id`, `Categories`.`seo_keyword`, `Categories`.`description`, `Categories`.`meta_description`, `Categories`.`meta_keywords`, `Categories`.`seo_title`, `Categories`.`seo_h1`, `Categories`.`store_ids`, `Categories`.`layout` FROM `Categories`;

            TRUNCATE TABLE `EXProducts`;
            INSERT INTO `EXProducts` ( `product_id`, `name`, `categories`, `main_categories`, `quantity`, `model`, `manufacturer`, `image_name`, `price`, `date_added`, `date_modified`, `date_available`, `seo_keyword`, `description`, `meta_description`, `meta_keywords`, `seo_title`, `seo_h1`, `tags` )
            SELECT `Products`.`product_id`, `Products`.`name`, `Products`.`categories`, `Products`.`main_categories`, `Products`.`quantity`, `Products`.`model`, `Products`.`manufacturer`, `Products`.`image_name`, `Products`.`price`, `Products`.`date_added`, `Products`.`date_modified`, `Products`.`date_available`, `Products`.`seo_keyword`, `Products`.`description`, `Products`.`meta_description`, `Products`.`meta_keywords`, `Products`.`seo_title`, `Products`.`seo_h1`, `Products`.`tags` FROM `Products`;

            TRUNCATE TABLE `oc_category`;
            INSERT INTO `oc_category` ( `category_id`, `image`, `parent_id`, `top`, `column`, `sort_order`, `status`, `date_added`, `date_modified` )
            SELECT `EXCategories`.`category_id`, `EXCategories`.`image_name`, `EXCategories`.`parent_id`, `EXCategories`.`top`, `EXCategories`.`columns`, `EXCategories`.`sort_order`, 1, `EXCategories`.`date_added`, `EXCategories`.`date_modified` FROM `EXCategories`;

            TRUNCATE TABLE `oc_category_description`;
            INSERT INTO `oc_category_description` ( `category_id`, `language_id`, `name`, `meta_description`, `seo_title`, `seo_h1`, `description` )
            SELECT `EXCategories`.`category_id`, 1, `EXCategories`.`name`, `EXCategories`.`meta_description`, `EXCategories`.`seo_title`, `EXCategories`.`seo_h1`, `EXCategories`.`description`
            FROM `EXCategories`;

            TRUNCATE TABLE `oc_category_path`;
            INSERT INTO `oc_category_path` ( `category_id`, `path_id`, `level`)
            SELECT `EXCategories`.`category_id`, `EXCategories`.`parent_id`, 0 FROM `EXCategories`;

            TRUNCATE TABLE `oc_category_to_store`;
            INSERT INTO `oc_category_to_store` ( `category_id`, `store_id` )
            SELECT `EXCategories`.`category_id`, 0 FROM `EXCategories`;

            TRUNCATE TABLE `oc_product`;
            INSERT INTO `oc_product` ( `product_id`, `model`, `quantity`, `image`, `manufacturer_id`, `price`, `date_available`, `date_added`, `date_modified` )
            SELECT `EXProducts`.`product_id`, `EXProducts`.`model`, `EXProducts`.`quantity`, `EXProducts`.`image_name`, `EXProducts`.`manufacturer`, `EXProducts`.`price`, `EXProducts`.`date_available`, `EXProducts`.`date_added`, `EXProducts`.`date_modified` FROM `EXProducts`;

            TRUNCATE TABLE `oc_product_description`;
            INSERT INTO `oc_product_description` ( `product_id`, `language_id`, `name`, `description`, `meta_description`, `seo_title`, `seo_h1`, `tag` )
            SELECT `EXProducts`.`product_id`, 1, `EXProducts`.`name`, `EXProducts`.`description`, `EXProducts`.`meta_description`, `EXProducts`.`seo_title`, `EXProducts`.`seo_h1`, `EXProducts`.`tags` FROM `EXProducts`;

            TRUNCATE TABLE `oc_product_to_store`;
            INSERT INTO `oc_product_to_store` (`product_id`)
            SELECT `EXProducts`.`product_id`
            FROM `EXProducts`;

            TRUNCATE TABLE `oc_product_image`;
            INSERT INTO `oc_product_image` (`product_id`, `image`, `sort_order`)
            SELECT `AdditionalImages`.`product_id`, `AdditionalImages`.`image`, `AdditionalImages`.`sort_order` FROM `AdditionalImages`;

            TRUNCATE TABLE `oc_product_to_category`;
            INSERT INTO `oc_product_to_category` (`product_id`, `category_id`, `main_category`)
            SELECT `EXProducts`.`product_id`, `EXProducts`.`categories`, `EXProducts`.`main_categories` FROM `EXProducts`;

            UPDATE `Options` INNER JOIN `oc_option_description` ON `Options`.`option` = `oc_option_description`.`name` SET `Options`.`option` = `oc_option_description`.`option_id`;

            TRUNCATE TABLE `oc_option_value_description`;
            INSERT INTO `oc_option_value_description` (`language_id`, `option_id`, `name`)
            SELECT 1, `Options`.`option`, `Options`.`value` FROM `Options`;

            TRUNCATE TABLE `oc_option_value`;
            INSERT INTO `oc_option_value` ( `option_value_id`, `option_id`, `sort_order` )
            SELECT `oc_option_value_description`.`option_value_id`, `oc_option_value_description`.`option_id`, 0
            FROM `oc_option_value_description`;

            TRUNCATE TABLE `oc_product_option`;
            INSERT INTO `oc_product_option` ( `product_id`, `option_id`, `required` )
            SELECT `Options`.`product_id`, `Options`.`option`, 1 FROM `Options`
            GROUP BY `Options`.`product_id`, `Options`.`option`
            HAVING (((Count(`Options`.`product_id`))>=1) And ((Count(`Options`.`option`))>=1));

            TRUNCATE TABLE `oc_product_option_value`;
            INSERT INTO `oc_product_option_value` ( `product_id`, `option_id`, `option_value_id` )
            SELECT `Options`.`product_id`, `Options`.`option`, `Options`.`value` FROM `Options`;

            UPDATE `oc_product_option_value` INNER JOIN `oc_product_option` ON (`oc_product_option_value`.`option_id` = `oc_product_option`.`option_id`) AND (`oc_product_option_value`.`product_id` = `oc_product_option`.`product_id`) SET `oc_product_option_value`.`product_option_id` = `oc_product_option`.`product_option_id`;

            UPDATE `oc_product_option_value` SET `option_value_id`= `product_option_value_id`;

            UPDATE (`Options` INNER JOIN `oc_option_value_description` ON `Options`.`value` = `oc_option_value_description`.`name`) INNER JOIN `oc_option_value` ON `oc_option_value_description`.`option_value_id` = `oc_option_value`.`option_value_id` SET `oc_option_value`.`sort_order` = `Options`.`sort_order`;

            TRUNCATE TABLE `oc_category_filter`;
            INSERT INTO `oc_category_filter` ( `category_id`, `filter_id` )
            SELECT `oc_category`.`category_id`, 1 FROM `oc_category`;

            TRUNCATE TABLE `oc_product_filter`;
            INSERT INTO `oc_product_filter` ( `product_id`, `filter_id` )
            SELECT `oc_product`.`product_id`, 1
            FROM `oc_product`
            WHERE (((`oc_product`.`quantity`)<>0));

            UPDATE `oc_category_description` INNER JOIN `category_description` ON `oc_category_description`.`category_id` = `category_description`.`category_id`
            SET`oc_category_description`.`name`=`category_description`.`name`,`oc_category_description`.`description`=`category_description`.`description`,`oc_category_description`.`meta_description`=`category_description`.`meta_description`,`oc_category_description`.`meta_keyword`=`category_description`.`meta_keyword`,`oc_category_description`.`seo_title`=`category_description`.`seo_title`,`oc_category_description`.`seo_h1`=`category_description`.`seo_h1`;

            TRUNCATE TABLE `aroms`;

            TRUNCATE TABLE `nearoms`;

            UPDATE `oc_product` INNER JOIN `oc_product_to_category` ON `oc_product`.`product_id` = `oc_product_to_category`.`product_id` SET `oc_product_to_category`.`category_id` = 10
            WHERE (((`oc_product`.`quantity`)=0));

            INSERT INTO `aroms` ( `ID`, `Status` )
            SELECT `Categories`.`category_id`, 0
            FROM `Categories` LEFT JOIN `oc_category` ON `Categories`.`category_id`=`oc_category`.`parent_id`
            WHERE (((`oc_category`.`parent_id`) IS NULL));

            INSERT INTO `nearoms` ( `ID`, `Status` )
            SELECT `oc_product_to_category`.`category_id`, 1
            FROM `oc_product_to_category`
            GROUP BY `oc_product_to_category`.`category_id`
            HAVING (((COUNT(`oc_product_to_category`.`category_id`))>=1));

            UPDATE `oc_category` INNER JOIN `aroms` ON `oc_category`.`category_id` = `aroms`.`ID` SET `oc_category`.`status` = "0";

            UPDATE `oc_category` INNER JOIN `nearoms` ON `oc_category`.`category_id` = `nearoms`.`ID` SET `oc_category`.`status` = "1";
            """
    elif portal == "butic":
        return """
            TRUNCATE TABLE `EXCategories`;
            INSERT INTO `EXCategories` ( `category_id`, `parent_id`, `name`, `top`, `columns`, `sort_order`, `image_name`, `date_added`, `date_modified`, `language_id`, `seo_keyword`, `description`, `meta_description`, `meta_keywords`, `seo_title`, `seo_h1`, `store_ids`, `layout`)
            SELECT `Categories`.`category_id`, `Categories`.`parent_id`, `Categories`.`name`, `Categories`.`top`, `Categories`.`columns`, `Categories`.`sort_order`, `Categories`.`image_name`, `Categories`.`date_added`, `Categories`.`date_modified`, `Categories`.`language_id`, `Categories`.`seo_keyword`, `Categories`.`description`, `Categories`.`meta_description`, `Categories`.`meta_keywords`, `Categories`.`seo_title`, `Categories`.`seo_h1`, `Categories`.`store_ids`, `Categories`.`layout` FROM `Categories`;


            TRUNCATE TABLE `EXProducts`;
            INSERT INTO `EXProducts` ( `product_id`, `name`, `categories`, `main_categories`, `quantity`, `model`, `manufacturer`, `image_name`, `price`, `date_added`, `date_modified`, `date_available`, `seo_keyword`, `description`, `meta_description`, `meta_keywords`, `seo_title`, `seo_h1`, `tags` )
            SELECT `Products`.`product_id`, `Products`.`name`, `Products`.`categories`, `Products`.`main_categories`, `Products`.`quantity`, `Products`.`model`, `Products`.`manufacturer`, `Products`.`image_name`, `Products`.`price`, `Products`.`date_added`, `Products`.`date_modified`, `Products`.`date_available`, `Products`.`seo_keyword`, `Products`.`description`, `Products`.`meta_description`, `Products`.`meta_keywords`, `Products`.`seo_title`, `Products`.`seo_h1`, `Products`.`tags` FROM `Products`;


            TRUNCATE TABLE `fd653_category`;
            INSERT INTO `fd653_category` ( `category_id`, `image`, `parent_id`, `top`, `column`, `sort_order`, `status`, `date_added`, `date_modified` )
            SELECT `EXCategories`.`category_id`, `EXCategories`.`image_name`, `EXCategories`.`parent_id`, `EXCategories`.`top`, 3, `EXCategories`.`sort_order`, 1, `EXCategories`.`date_added`, `EXCategories`.`date_modified` FROM `EXCategories`;

            TRUNCATE TABLE `fd653_category_description`;
            INSERT INTO `fd653_category_description` ( `category_id`, `language_id`, `name`, `meta_title`, `meta_description`, `description`, `meta_keyword`, `meta_h1` )
            SELECT `EXCategories`.`category_id`, 1, `EXCategories`.`name`, `EXCategories`.`seo_title`, `EXCategories`.`meta_description`, `EXCategories`.`description`, `EXCategories`.`seo_keyword`, `EXCategories`.`seo_h1`
            FROM `EXCategories`;


            TRUNCATE TABLE `fd653_category_path`;
            INSERT INTO `fd653_category_path` ( `category_id`, `path_id`, `level`)
            SELECT `EXCategories`.`category_id`, `EXCategories`.`parent_id`, 0 FROM `EXCategories`;


            TRUNCATE TABLE `fd653_category_to_store`;
            INSERT INTO `fd653_category_to_store` ( `category_id`, `store_id` )
            SELECT `EXCategories`.`category_id`, 0 FROM `EXCategories`;

            TRUNCATE TABLE `fd653_category_to_layout`;
            INSERT INTO `fd653_category_to_layout` ( `category_id`, `store_id`, `layout_id` )
            SELECT `EXCategories`.`category_id`, 0, 0 FROM `EXCategories`;

            INSERT INTO `fd653_category_to_layout` ( `category_id`, `store_id`, `layout_id` )
            SELECT `EXCategories`.`category_id`, 1, 0 FROM `EXCategories`;


            TRUNCATE TABLE `fd653_product`;
            INSERT INTO `fd653_product` ( `product_id`, `model`, `quantity`, `image`, `manufacturer_id`, `price`, `date_available`, `date_added`, `date_modified` )
            SELECT `EXProducts`.`product_id`, `EXProducts`.`model`, `EXProducts`.`quantity`, `EXProducts`.`image_name`, `EXProducts`.`manufacturer`, `EXProducts`.`price`, `EXProducts`.`date_available`, `EXProducts`.`date_added`, `EXProducts`.`date_modified` FROM `EXProducts`;


            TRUNCATE TABLE `fd653_product_description`;
            INSERT INTO `fd653_product_description` ( `product_id`, `language_id`, `name`, `description`, `meta_description`, `tag` )
            SELECT `EXProducts`.`product_id`, 1, `EXProducts`.`name`, `EXProducts`.`description`, `EXProducts`.`meta_description`, `EXProducts`.`tags` FROM `EXProducts`;



            TRUNCATE TABLE `fd653_product_to_store`;
            INSERT INTO `fd653_product_to_store` (`product_id`, `store_id`)
            SELECT `EXProducts`.`product_id`, 0
            FROM `EXProducts`;


            INSERT INTO `fd653_product_to_store` (`product_id`, `store_id`)
            SELECT `EXProducts`.`product_id`, 1
            FROM `EXProducts`
            INNER JOIN `Products` ON `EXProducts`.`product_id`=`Products`.`product_id`
            WHERE `Products`.`upc` = 2;


            TRUNCATE TABLE `fd653_product_image`;
            INSERT INTO `fd653_product_image` (`product_id`, `image`, `sort_order`)
            SELECT `AdditionalImages`.`product_id`, `AdditionalImages`.`image`, `AdditionalImages`.`sort_order` FROM `AdditionalImages`;


            TRUNCATE TABLE `fd653_product_to_category`;
            INSERT INTO `fd653_product_to_category` (`product_id`, `category_id`, `main_category`)
            SELECT `EXProducts`.`product_id`, `EXProducts`.`categories`, `EXProducts`.`main_categories` FROM `EXProducts`;

            TRUNCATE TABLE `fd653_product_to_layout`;
            INSERT INTO `fd653_product_to_layout` (`product_id`, `store_id`, `layout_id`)
            SELECT `EXProducts`.`product_id`, 0, 0 FROM `EXProducts`;

            INSERT INTO `fd653_product_to_layout` (`product_id`, `store_id`, `layout_id`)
            SELECT `EXProducts`.`product_id`, 1, 0 FROM `EXProducts`;

            UPDATE `Options` INNER JOIN `fd653_option_description` ON `Options`.`option` = `fd653_option_description`.`name` SET `Options`.`option` = `fd653_option_description`.`option_id`;


            TRUNCATE TABLE `fd653_option_value_description`;
            INSERT INTO `fd653_option_value_description` (`language_id`, `option_id`, `name`)
            SELECT 1, `Options`.`option`, `Options`.`value` FROM `Options`;


            TRUNCATE TABLE `fd653_option_value`;
            INSERT INTO `fd653_option_value` ( `option_value_id`, `option_id`, `sort_order` )
            SELECT `fd653_option_value_description`.`option_value_id`, `fd653_option_value_description`.`option_id`, 0
            FROM `fd653_option_value_description`;


            TRUNCATE TABLE `fd653_product_option`;
            INSERT INTO `fd653_product_option` ( `product_id`, `option_id`, `required` )
            SELECT `Options`.`product_id`, `Options`.`option`, 1 FROM `Options`
            GROUP BY `Options`.`product_id`, `Options`.`option`
            HAVING (((Count(`Options`.`product_id`))>=1) And ((Count(`Options`.`option`))>=1));


            TRUNCATE TABLE `fd653_product_option_value`;
            INSERT INTO `fd653_product_option_value` ( `product_id`, `option_id`, `option_value_id` )
            SELECT `Options`.`product_id`, `Options`.`option`, `Options`.`value` FROM `Options`;


            UPDATE `fd653_product_option_value` INNER JOIN `fd653_product_option` ON (`fd653_product_option_value`.`option_id` = `fd653_product_option`.`option_id`) AND (`fd653_product_option_value`.`product_id` = `fd653_product_option`.`product_id`) SET `fd653_product_option_value`.`product_option_id` = `fd653_product_option`.`product_option_id`;

            UPDATE `fd653_product_option_value` SET `option_value_id`= `product_option_value_id`;


            UPDATE (`Options` INNER JOIN `fd653_option_value_description` ON `Options`.`value` = `fd653_option_value_description`.`name`) INNER JOIN `fd653_option_value` ON `fd653_option_value_description`.`option_value_id` = `fd653_option_value`.`option_value_id` SET `fd653_option_value`.`sort_order` = `Options`.`sort_order`;

            TRUNCATE TABLE `fd653_product_discount`;

            INSERT INTO `fd653_product_discount` ( `product_id`, `price`, `customer_group_id`, `quantity`, `priority` )
            SELECT `Products`.`product_id`, `Products`.`price2`, 2 , 1, 1 FROM `Products`;

            UPDATE `fd653_product` INNER JOIN `Products` ON `fd653_product`.`product_id` = `Products`.`product_id` SET `fd653_product`.`isbn` = `Products`.`shipdate`;

            UPDATE `fd653_product` INNER JOIN `Products` ON `fd653_product`.`product_id` = `Products`.`product_id` SET `fd653_product`.`mpn` = `Products`.`mpn`;

            TRUNCATE TABLE `wait_order`;

            TRUNCATE TABLE `wait_order_product`;

            INSERT INTO `wait_order` ( `order_id` ) SELECT `fd653_order`.`order_id` FROM `fd653_order` WHERE (((`fd653_order`.`order_status_id`)<>"5"));

            INSERT INTO `wait_order_product` ( `order_id`, `product_id`, `name`, `price` ) SELECT `fd653_order_product`.`order_id`, `fd653_order_product`.`product_id`, `fd653_order_product`.`name`, `fd653_order_product`.`price` FROM `fd653_order_product` INNER JOIN `wait_order` ON `fd653_order_product`.`order_id` = `wait_order`.`order_id`;

            UPDATE `fd653_product` SET `fd653_product`.`model` = NULL;

            UPDATE `fd653_product` INNER JOIN `wait_order_product` ON `fd653_product`.`product_id` = `wait_order_product`.`product_id` SET `fd653_product`.`model` = `wait_order_product`.`price`;

            UPDATE `wait_order_product` INNER JOIN `fd653_product` ON `wait_order_product`.`product_id` = `fd653_product`.`product_id` SET `wait_order_product`.`new_price` = `fd653_product`.`price`;

            UPDATE `wait_order` INNER JOIN `wait_order_product` ON `wait_order`.`order_id` = `wait_order_product`.`order_id` SET `wait_order`.`need_mail` = 1 WHERE (((`wait_order_product`.`price`)<>`wait_order_product`.`new_price`));

            TRUNCATE TABLE `fd653_category_filter`;
            INSERT INTO `fd653_category_filter` ( `category_id`, `filter_id` )
            SELECT `fd653_category`.`category_id`, 3 FROM `fd653_category`;

            UPDATE `Products` INNER JOIN `fd653_product` ON `Products`.`product_id` = `fd653_product`.`product_id` SET `fd653_product`.`status` = 2
            WHERE (((`Products`.`upc`)= 2));

            UPDATE `fd653_category` INNER JOIN (`fd653_product_to_category` INNER JOIN `fd653_product` ON `fd653_product_to_category`.`product_id` = `fd653_product`.`product_id`) ON `fd653_category`.`category_id` = `fd653_product_to_category`.`category_id` SET `fd653_category`.`status` = 2
            WHERE (((`fd653_product`.`status`)= 2));

            TRUNCATE TABLE `Brands`;

            INSERT INTO `Brands` ( `category_id` ) SELECT DISTINCT `fd653_category`.`parent_id` FROM `fd653_category` WHERE (((`fd653_category`.`status`)= 2));

            UPDATE `fd653_category` INNER JOIN `Brands` ON `fd653_category`.`category_id` = `Brands`.`category_id` SET `fd653_category`.`status` = 2;

            TRUNCATE TABLE `Brands`;

            INSERT INTO `Brands` ( `category_id` ) SELECT DISTINCT `fd653_category`.`parent_id` FROM `fd653_category` WHERE (((`fd653_category`.`status`)= 2));

            UPDATE `fd653_category` INNER JOIN `Brands` ON `fd653_category`.`category_id` = `Brands`.`category_id` SET `fd653_category`.`status` = 2;

            TRUNCATE TABLE `Brands`;

            INSERT INTO `Brands` ( `category_id` ) SELECT DISTINCT `fd653_category`.`parent_id` FROM `fd653_category` WHERE (((`fd653_category`.`status`)= 2));

            UPDATE `fd653_category` INNER JOIN `Brands` ON `fd653_category`.`category_id` = `Brands`.`category_id` SET `fd653_category`.`status` = 2;

            UPDATE `fd653_product` SET `fd653_product`.`status` = 1;

            UPDATE `Products` INNER JOIN `fd653_product` ON `Products`.`product_id` = `fd653_product`.`product_id` SET `fd653_product`.`upc` = 2 WHERE (((`Products`.`upc`)=2));

            UPDATE `Products` INNER JOIN `fd653_product` ON `Products`.`product_id` = `fd653_product`.`product_id` SET `fd653_product`.`ean` = `Products`.`ean`;

            UPDATE `Products` INNER JOIN `fd653_product` ON `Products`.`product_id` = `fd653_product`.`product_id` SET `fd653_product`.`jan` = `Products`.`jan`;

            UPDATE `fd653_category` SET `status`=1;

            UPDATE `fd653_category` pc INNER JOIN `fd653_category_description` pcd ON pc.`category_id` = pcd.`category_id` SET pc.`status` = 0 WHERE pcd.`name` = "Селективы";

            UPDATE `fd653_category` pc INNER JOIN `fd653_category_description` pcd ON pc.`category_id` = pcd.`category_id` SET pc.`status` = 0 WHERE pcd.`name` = "Выпали из прайса";

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `fd653_product_to_category`.`category_id` FROM `fd653_product_to_category` INNER JOIN (SELECT `fd653_product_to_store`.`product_id` FROM `fd653_product_to_store` INNER JOIN `fd653_product_to_category` ON `fd653_product_to_store`.`product_id` = `fd653_product_to_category`.`product_id` WHERE (((`fd653_product_to_store`.`store_id`)="1"))) S ON `fd653_product_to_category`.`product_id` = S.`product_id`;

            UPDATE `helper` SET `helper`.`level` = 4;

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `fd653_category`.`parent_id` FROM `fd653_category` INNER JOIN `helper` ON `fd653_category`.`category_id` = `helper`.`category_id`;

            UPDATE `helper` SET `helper`.`level` = 3 WHERE `helper`.`level` = 0;

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `fd653_category`.`parent_id` FROM `fd653_category` INNER JOIN `helper` ON `fd653_category`.`category_id` = `helper`.`category_id` WHERE `helper`.`level` = 3;

            UPDATE `helper` SET `helper`.`level` = 2 WHERE `helper`.`level` = 0;

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `fd653_category`.`parent_id` FROM `fd653_category` INNER JOIN `helper` ON `fd653_category`.`category_id` = `helper`.`category_id` WHERE `helper`.`level` = 2;

            UPDATE `helper` SET `helper`.`level` = 1 WHERE `helper`.`level` = 0;

            INSERT INTO `fd653_category_to_store` (`category_id`,`store_id`) SELECT DISTINCT `helper`.`category_id`, 1 FROM `helper`;

            TRUNCATE TABLE `helper`;

            INSERT INTO `helper2` (`id`) SELECT `fd653_category`.`category_id` FROM `fd653_category` WHERE `fd653_category`.`top`=1;

            UPDATE `fd653_category` c SET c.`top` = 1 WHERE c.`parent_id` IN (SELECT * FROM `helper2`);

            TRUNCATE TABLE `helper2`;

            INSERT INTO `helper3` (`category_id`, `level`)
            SELECT `fd653_category`.`category_id`, 0
            FROM `fd653_category`
            WHERE `fd653_category`.`parent_id` = 9;

            INSERT IGNORE INTO `helper3` (`category_id`, `level`)
            SELECT `fd653_category`.`category_id`, 1
            FROM `fd653_category`
                JOIN `helper3` h ON `fd653_category`.`parent_id` = h.`category_id`;

            INSERT IGNORE INTO `helper3` (`category_id`, `level`)
            SELECT `fd653_category`.`category_id`, 2
            FROM `fd653_category`
                JOIN `helper3` h ON `fd653_category`.`parent_id` = h.`category_id`;

            INSERT IGNORE INTO `helper3` (`category_id`, `level`)
            SELECT `fd653_category`.`category_id`, 3
            FROM `fd653_category`
                JOIN `helper3` h ON `fd653_category`.`parent_id` = h.`category_id`;

            UPDATE `fd653_product` p
            JOIN `fd653_product_to_category` pc ON p.`product_id` = pc.`product_id`
            JOIN `helper3` h ON pc.`category_id` = h.`category_id`
            SET p.`image` = 'bottle.jpg'
            WHERE p.`image` = '';

            TRUNCATE `helper3`;

            INSERT INTO `fd653_product_special` (`product_id`, `customer_group_id`, `price`, `date_start`, `date_end`)
            SELECT `Products`.`product_id`, 2, `Products`.`price2`, NOW(), `Products`.`shipdate`
            FROM `Products`
            WHERE `Products`.`price2` <>"";

            UPDATE fd653_product pp INNER JOIN fd653_product_to_store ps ON pp.product_id=ps.product_id SET pp.upc=1 WHERE ps.store_id=1;

            UPDATE fd653_product_description pd SET pd.meta_description = CONCAT(pd.name, " — ", "доставим курьером в любой район Новосибирска или транспортной компанией по всей России"), pd.meta_keyword = pd.name;
        """
    elif portal == "ismy":
        return """
            TRUNCATE TABLE `EXCategories`;
            INSERT INTO `EXCategories` ( `category_id`, `parent_id`, `name`, `top`, `columns`, `sort_order`, `image_name`, `date_added`, `date_modified`, `language_id`, `seo_keyword`, `description`, `meta_description`, `meta_keywords`, `seo_title`, `seo_h1`, `store_ids`, `layout`)
            SELECT `Categories`.`category_id`, `Categories`.`parent_id`, `Categories`.`name`, `Categories`.`top`, `Categories`.`columns`, `Categories`.`sort_order`, `Categories`.`image_name`, `Categories`.`date_added`, `Categories`.`date_modified`, `Categories`.`language_id`, `Categories`.`seo_keyword`, `Categories`.`description`, `Categories`.`meta_description`, `Categories`.`meta_keywords`, `Categories`.`seo_title`, `Categories`.`seo_h1`, `Categories`.`store_ids`, `Categories`.`layout` FROM `Categories`;


            TRUNCATE TABLE `EXProducts`;
            INSERT INTO `EXProducts` ( `product_id`, `name`, `categories`, `main_categories`, `quantity`, `model`, `manufacturer`, `image_name`, `price`, `date_added`, `date_modified`, `date_available`, `seo_keyword`, `description`, `meta_description`, `meta_keywords`, `seo_title`, `seo_h1`, `tags` )
            SELECT `Products`.`product_id`, `Products`.`name`, `Products`.`categories`, `Products`.`main_categories`, `Products`.`quantity`, `Products`.`model`, `Products`.`manufacturer`, `Products`.`image_name`, `Products`.`price`, `Products`.`date_added`, `Products`.`date_modified`, `Products`.`date_available`, `Products`.`seo_keyword`, `Products`.`description`, `Products`.`meta_description`, `Products`.`meta_keywords`, `Products`.`seo_title`, `Products`.`seo_h1`, `Products`.`tags` FROM `Products`;


            TRUNCATE TABLE `p43j_category`;
            INSERT INTO `p43j_category` ( `category_id`, `image`, `parent_id`, `top`, `column`, `sort_order`, `status`, `date_added`, `date_modified` )
            SELECT `EXCategories`.`category_id`, `EXCategories`.`image_name`, `EXCategories`.`parent_id`, `EXCategories`.`top`, 3, `EXCategories`.`sort_order`, 1, `EXCategories`.`date_added`, `EXCategories`.`date_modified` FROM `EXCategories`;

            TRUNCATE TABLE `p43j_category_description`;
            INSERT INTO `p43j_category_description` ( `category_id`, `language_id`, `name`, `meta_title`, `meta_description`, `description`, `meta_keyword`, `meta_h1` )
            SELECT `EXCategories`.`category_id`, 1, `EXCategories`.`name`, `EXCategories`.`seo_title`, `EXCategories`.`meta_description`, `EXCategories`.`description`, `EXCategories`.`seo_keyword`, `EXCategories`.`seo_h1`
            FROM `EXCategories`;


            TRUNCATE TABLE `p43j_category_path`;
            INSERT INTO `p43j_category_path` ( `category_id`, `path_id`, `level`)
            SELECT `EXCategories`.`category_id`, `EXCategories`.`parent_id`, 0 FROM `EXCategories`;


            TRUNCATE TABLE `p43j_category_to_store`;
            INSERT INTO `p43j_category_to_store` ( `category_id`, `store_id` )
            SELECT `EXCategories`.`category_id`, 0 FROM `EXCategories`;

            TRUNCATE TABLE `p43j_category_to_layout`;
            INSERT INTO `p43j_category_to_layout` ( `category_id`, `store_id`, `layout_id` )
            SELECT `EXCategories`.`category_id`, 0, 0 FROM `EXCategories`;

            INSERT INTO `p43j_category_to_layout` ( `category_id`, `store_id`, `layout_id` )
            SELECT `EXCategories`.`category_id`, 1, 0 FROM `EXCategories`;


            TRUNCATE TABLE `p43j_product`;
            INSERT INTO `p43j_product` ( `product_id`, `model`, `quantity`, `image`, `manufacturer_id`, `price`, `date_available`, `date_added`, `date_modified` )
            SELECT `EXProducts`.`product_id`, `EXProducts`.`model`, `EXProducts`.`quantity`, `EXProducts`.`image_name`, `EXProducts`.`manufacturer`, `EXProducts`.`price`, `EXProducts`.`date_available`, `EXProducts`.`date_added`, `EXProducts`.`date_modified` FROM `EXProducts`;


            TRUNCATE TABLE `p43j_product_description`;
            INSERT INTO `p43j_product_description` ( `product_id`, `language_id`, `name`, `description`, `meta_description`, `tag` )
            SELECT `EXProducts`.`product_id`, 1, `EXProducts`.`name`, `EXProducts`.`description`, `EXProducts`.`meta_description`, `EXProducts`.`tags` FROM `EXProducts`;


            TRUNCATE TABLE `p43j_product_to_store`;
            INSERT INTO `p43j_product_to_store` (`product_id`, `store_id`)
            SELECT `EXProducts`.`product_id`, 0
            FROM `EXProducts`;

            INSERT INTO `delivery_types_helper` (`date`)
            SELECT DISTINCT `Products`.`shipdate`
            FROM `Products`;

            SET @dates = (SELECT `delivery_types_helper`.`date` FROM `delivery_types_helper` ORDER BY (CONCAT(SUBSTRING(`delivery_types_helper`.`date`, 7, 2),".",SUBSTRING(`delivery_types_helper`.`date`, 4, 2),".",SUBSTRING(`delivery_types_helper`.`date`, 1, 2))) LIMIT 1);
            UPDATE `delivery_types` dt SET dt.`date` = @dates WHERE dt.name="FAST";

            SET @dates = (SELECT `delivery_types_helper`.`date` FROM `delivery_types_helper` ORDER BY (CONCAT(SUBSTRING(`delivery_types_helper`.`date`, 7, 2),".",SUBSTRING(`delivery_types_helper`.`date`, 4, 2),".",SUBSTRING(`delivery_types_helper`.`date`, 1, 2))) DESC LIMIT 1);
            UPDATE `delivery_types` dt SET dt.`date` = @dates WHERE dt.name="SLOW";

            UPDATE `delivery_types` SET `date_as_date`=(CONCAT(SUBSTRING(`date`, 7, 2),".",SUBSTRING(`date`, 4, 2),".",SUBSTRING(`date`, 1, 2)));

            TRUNCATE TABLE `delivery_types_helper`;

            INSERT INTO `p43j_product_to_store` (`product_id`, `store_id`)
            SELECT `EXProducts`.`product_id`, 1
            FROM `EXProducts`
            INNER JOIN `Products` ON `EXProducts`.`product_id`=`Products`.`product_id`
            WHERE `Products`.`shipdate` = (SELECT `delivery_types`.`date` FROM `delivery_types` WHERE `delivery_types`.`name` = 'FAST');

            INSERT INTO `p43j_product_to_store` (`product_id`, `store_id`)
            SELECT `EXProducts`.`product_id`, 1
            FROM `EXProducts`
            INNER JOIN `Products` ON `EXProducts`.`product_id`=`Products`.`product_id`
            WHERE `Products`.`shipdate` = (SELECT `delivery_types`.`date` FROM `delivery_types` WHERE `delivery_types`.`name` = 'NOT_SO_FAST');

            TRUNCATE TABLE `p43j_product_image`;
            INSERT INTO `p43j_product_image` (`product_id`, `image`, `sort_order`)
            SELECT `AdditionalImages`.`product_id`, `AdditionalImages`.`image`, `AdditionalImages`.`sort_order` FROM `AdditionalImages`;


            TRUNCATE TABLE `p43j_product_to_category`;
            INSERT INTO `p43j_product_to_category` (`product_id`, `category_id`, `main_category`)
            SELECT `EXProducts`.`product_id`, `EXProducts`.`categories`, `EXProducts`.`main_categories` FROM `EXProducts`;

            TRUNCATE TABLE `p43j_product_to_layout`;
            INSERT INTO `p43j_product_to_layout` (`product_id`, `store_id`, `layout_id`)
            SELECT `EXProducts`.`product_id`, 0, 0 FROM `EXProducts`;

            INSERT INTO `p43j_product_to_layout` (`product_id`, `store_id`, `layout_id`)
            SELECT `EXProducts`.`product_id`, 1, 0 FROM `EXProducts`;

            UPDATE `Options` INNER JOIN `p43j_option_description` ON `Options`.`option` = `p43j_option_description`.`name` SET `Options`.`option` = `p43j_option_description`.`option_id`;


            TRUNCATE TABLE `p43j_option_value_description`;
            INSERT INTO `p43j_option_value_description` (`language_id`, `option_id`, `name`)
            SELECT 1, `Options`.`option`, `Options`.`value` FROM `Options`;


            TRUNCATE TABLE `p43j_option_value`;
            INSERT INTO `p43j_option_value` ( `option_value_id`, `option_id`, `sort_order` )
            SELECT `p43j_option_value_description`.`option_value_id`, `p43j_option_value_description`.`option_id`, 0
            FROM `p43j_option_value_description`;


            TRUNCATE TABLE `p43j_product_option`;
            INSERT INTO `p43j_product_option` ( `product_id`, `option_id`, `required` )
            SELECT `Options`.`product_id`, `Options`.`option`, 1 FROM `Options`
            GROUP BY `Options`.`product_id`, `Options`.`option`
            HAVING (((Count(`Options`.`product_id`))>=1) And ((Count(`Options`.`option`))>=1));


            TRUNCATE TABLE `p43j_product_option_value`;
            INSERT INTO `p43j_product_option_value` ( `product_id`, `option_id`, `option_value_id` )
            SELECT `Options`.`product_id`, `Options`.`option`, `Options`.`value` FROM `Options`;


            UPDATE `p43j_product_option_value` INNER JOIN `p43j_product_option` ON (`p43j_product_option_value`.`option_id` = `p43j_product_option`.`option_id`) AND (`p43j_product_option_value`.`product_id` = `p43j_product_option`.`product_id`) SET `p43j_product_option_value`.`product_option_id` = `p43j_product_option`.`product_option_id`;

            UPDATE `p43j_product_option_value` SET `option_value_id`= `product_option_value_id`;


            UPDATE `Options` INNER JOIN `p43j_option_value_description` ON `Options`.`value` = `p43j_option_value_description`.`name` INNER JOIN `p43j_option_value` ON `p43j_option_value_description`.`option_value_id` = `p43j_option_value`.`option_value_id` SET `p43j_option_value`.`sort_order` = `Options`.`sort_order`;

            TRUNCATE TABLE `p43j_product_discount`;

            INSERT INTO `p43j_product_discount` ( `product_id`, `price`, `customer_group_id`, `quantity`, `priority` )
            SELECT `Products`.`product_id`, `Products`.`price2`, 2 , 1, 1 FROM `Products`;

            UPDATE `p43j_product` INNER JOIN `Products` ON `p43j_product`.`product_id` = `Products`.`product_id` SET `p43j_product`.`isbn` = `Products`.`shipdate`;

            UPDATE `p43j_product` INNER JOIN `Products` ON `p43j_product`.`product_id` = `Products`.`product_id` SET `p43j_product`.`mpn` = `Products`.`mpn`;

            TRUNCATE TABLE `wait_order`;

            TRUNCATE TABLE `wait_order_product`;

            INSERT INTO `wait_order` ( `order_id` ) SELECT `p43j_order`.`order_id` FROM `p43j_order` WHERE (((`p43j_order`.`order_status_id`)<>"5"));

            INSERT INTO `wait_order_product` ( `order_id`, `product_id`, `name`, `price` ) SELECT `p43j_order_product`.`order_id`, `p43j_order_product`.`product_id`, `p43j_order_product`.`name`, `p43j_order_product`.`price` FROM `p43j_order_product` INNER JOIN `wait_order` ON `p43j_order_product`.`order_id` = `wait_order`.`order_id`;

            UPDATE `p43j_product` SET `p43j_product`.`model` = NULL;

            UPDATE `p43j_product` INNER JOIN `wait_order_product` ON `p43j_product`.`product_id` = `wait_order_product`.`product_id` SET `p43j_product`.`model` = `wait_order_product`.`price`;

            UPDATE `wait_order_product` INNER JOIN `p43j_product` ON `wait_order_product`.`product_id` = `p43j_product`.`product_id` SET `wait_order_product`.`new_price` = `p43j_product`.`price`;

            UPDATE `wait_order` INNER JOIN `wait_order_product` ON `wait_order`.`order_id` = `wait_order_product`.`order_id` SET `wait_order`.`need_mail` = 1 WHERE (((`wait_order_product`.`price`)<>`wait_order_product`.`new_price`));

            TRUNCATE TABLE `p43j_category_filter`;
            INSERT INTO `p43j_category_filter` ( `category_id`, `filter_id` )
            SELECT `p43j_category`.`category_id`, 3 FROM `p43j_category`;

            UPDATE `Products` INNER JOIN `p43j_product` ON `Products`.`product_id` = `p43j_product`.`product_id` SET `p43j_product`.`status` = 2
            WHERE (((`Products`.`upc`)= 2));

            UPDATE `p43j_category` INNER JOIN (`p43j_product_to_category` INNER JOIN `p43j_product` ON `p43j_product_to_category`.`product_id` = `p43j_product`.`product_id`) ON `p43j_category`.`category_id` = `p43j_product_to_category`.`category_id` SET `p43j_category`.`status` = 2
            WHERE (((`p43j_product`.`status`)= 2));

            TRUNCATE TABLE `Brands`;

            INSERT INTO `Brands` ( `category_id` ) SELECT DISTINCT `p43j_category`.`parent_id` FROM `p43j_category` WHERE (((`p43j_category`.`status`)= 2));

            UPDATE `p43j_category` INNER JOIN `Brands` ON `p43j_category`.`category_id` = `Brands`.`category_id` SET `p43j_category`.`status` = 2;

            TRUNCATE TABLE `Brands`;

            INSERT INTO `Brands` ( `category_id` ) SELECT DISTINCT `p43j_category`.`parent_id` FROM `p43j_category` WHERE (((`p43j_category`.`status`)= 2));

            UPDATE `p43j_category` INNER JOIN `Brands` ON `p43j_category`.`category_id` = `Brands`.`category_id` SET `p43j_category`.`status` = 2;

            TRUNCATE TABLE `Brands`;

            INSERT INTO `Brands` ( `category_id` ) SELECT DISTINCT `p43j_category`.`parent_id` FROM `p43j_category` WHERE (((`p43j_category`.`status`)= 2));

            UPDATE `p43j_category` INNER JOIN `Brands` ON `p43j_category`.`category_id` = `Brands`.`category_id` SET `p43j_category`.`status` = 2;

            UPDATE `p43j_product` SET `p43j_product`.`status` = 1;

            UPDATE `Products` INNER JOIN `p43j_product` ON `Products`.`product_id` = `p43j_product`.`product_id` SET `p43j_product`.`upc` = 2 WHERE (((`Products`.`upc`)=2));

            UPDATE `Products` INNER JOIN `p43j_product` ON `Products`.`product_id` = `p43j_product`.`product_id` SET `p43j_product`.`ean` = `Products`.`ean`;

            UPDATE `Products` INNER JOIN `p43j_product` ON `Products`.`product_id` = `p43j_product`.`product_id` SET `p43j_product`.`jan` = `Products`.`jan`;

            UPDATE `p43j_category` SET `status`=1;

            UPDATE `p43j_category` pc INNER JOIN `p43j_category_description` pcd ON pc.`category_id` = pcd.`category_id` SET pc.`status` = 0 WHERE pcd.`name` = "Селективы";

            UPDATE `p43j_category` pc INNER JOIN `p43j_category_description` pcd ON pc.`category_id` = pcd.`category_id` SET pc.`status` = 0 WHERE pcd.`name` = "Выпали из прайса";

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `p43j_product_to_category`.`category_id` FROM `p43j_product_to_category` INNER JOIN (SELECT `p43j_product_to_store`.`product_id` FROM `p43j_product_to_store` INNER JOIN `p43j_product_to_category` ON `p43j_product_to_store`.`product_id` = `p43j_product_to_category`.`product_id` WHERE (((`p43j_product_to_store`.`store_id`)="1"))) S ON `p43j_product_to_category`.`product_id` = S.`product_id`;

            UPDATE `helper` SET `helper`.`level` = 4;

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `p43j_category`.`parent_id` FROM `p43j_category` INNER JOIN `helper` ON `p43j_category`.`category_id` = `helper`.`category_id`;

            UPDATE `helper` SET `helper`.`level` = 3 WHERE `helper`.`level` = 0;

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `p43j_category`.`parent_id` FROM `p43j_category` INNER JOIN `helper` ON `p43j_category`.`category_id` = `helper`.`category_id` WHERE `helper`.`level` = 3;

            UPDATE `helper` SET `helper`.`level` = 2 WHERE `helper`.`level` = 0;

            INSERT INTO `helper` (`category_id`) SELECT DISTINCT `p43j_category`.`parent_id` FROM `p43j_category` INNER JOIN `helper` ON `p43j_category`.`category_id` = `helper`.`category_id` WHERE `helper`.`level` = 2;

            UPDATE `helper` SET `helper`.`level` = 1 WHERE `helper`.`level` = 0;

            INSERT INTO `p43j_category_to_store` (`category_id`,`store_id`) SELECT `helper`.`category_id`, 1 FROM `helper`;

            TRUNCATE TABLE `helper`;

            INSERT INTO `helper2` (`id`) SELECT `p43j_category`.`category_id` FROM `p43j_category` WHERE `p43j_category`.`top`=1;

            UPDATE `p43j_category` c SET c.`top` = 1 WHERE c.`parent_id` IN (SELECT * FROM `helper2`);

            TRUNCATE TABLE `helper2`;

            INSERT INTO `helper3` (`category_id`, `level`)
            SELECT `p43j_category`.`category_id`, 0
            FROM `p43j_category`
            WHERE `p43j_category`.`parent_id` = 9;

            INSERT IGNORE INTO `helper3` (`category_id`, `level`)
            SELECT `p43j_category`.`category_id`, 1
            FROM `p43j_category`
                JOIN `helper3` h ON `p43j_category`.`parent_id` = h.`category_id`;

            INSERT IGNORE INTO `helper3` (`category_id`, `level`)
            SELECT `p43j_category`.`category_id`, 2
            FROM `p43j_category`
                JOIN `helper3` h ON `p43j_category`.`parent_id` = h.`category_id`;

            INSERT IGNORE INTO `helper3` (`category_id`, `level`)
            SELECT `p43j_category`.`category_id`, 3
            FROM `p43j_category`
                JOIN `helper3` h ON `p43j_category`.`parent_id` = h.`category_id`;

            UPDATE `p43j_product` p
            JOIN `p43j_product_to_category` pc ON p.`product_id` = pc.`product_id`
            JOIN `helper3` h ON pc.`category_id` = h.`category_id`
            SET p.`image` = 'bottle.jpg'
            WHERE p.`image` = '';

            TRUNCATE `helper3`;
        """


def get_files_tables(portal: str) -> list[tuple[str, str]] | None:
    if portal == "ornam":
        return [
            ("data/ornam/AdditionalImages.txt", "AdditionalImages"),
            ("data/ornam/Categories.txt", "Categories"),
            ("data/ornam/Options.txt", "Options"),
            ("data/ornam/Products.txt", "Products"),
        ]
    elif portal == "butic":
        return [
            ("data/butic/AdditionalImages.txt", "AdditionalImages"),
            ("data/butic/Categories.txt", "Categories"),
            ("data/butic/Products1.txt", "Products"),
        ]
    elif portal == "ismy":
        return [
            ("data/ismy/AdditionalImages.txt", "AdditionalImages"),
            ("data/ismy/Categories.txt", "Categories"),
            ("data/ismy/Products.txt", "Products"),
        ]
    return None


def get_tables_for_overload(page: int | None) -> list[str]:
    if page is None:
        return [
            "p43j_category",
            "p43j_category_description",
            "p43j_category_filter",
            "p43j_category_path",
            "p43j_category_to_layout",
            "p43j_category_to_store",
            "p43j_manufacturer",
            "p43j_manufacturer_description",
            "p43j_manufacturer_to_layout",
            "p43j_manufacturer_to_store",
            # 'p43j_product',
            "p43j_product_attribute",
            "p43j_product_description",
            "p43j_product_discount",
            "p43j_product_filter",
            "p43j_product_image",
            "p43j_product_option",
            "p43j_product_option_value",
            "p43j_product_recurring",
            "p43j_product_related",
            "p43j_product_related_article",
            "p43j_product_related_mn",
            "p43j_product_related_wb",
            "p43j_product_reward",
            "p43j_product_special",
            "p43j_product_tab",
            "p43j_product_tab_desc",
            "p43j_product_to_benefit",
            "p43j_product_to_category",
            "p43j_product_to_download",
            "p43j_product_to_layout",
            "p43j_product_to_sticker",
            "p43j_product_to_store",
        ]
    else:
        return ["p43j_product"]


def get_tables_for_export(part: int | None) -> list[str]:
    if part == 1:
        return [
            "p43j_category",
            "p43j_category_description",
            "p43j_category_filter",
            "p43j_category_path",
            "p43j_category_to_layout",
            "p43j_category_to_store",
            "p43j_manufacturer",
            "p43j_manufacturer_description",
            "p43j_manufacturer_to_layout",
            "p43j_manufacturer_to_store",
            "p43j_product",
            "p43j_product_attribute",
            "p43j_product_description",
            "p43j_product_discount",
            "p43j_product_filter",
            "p43j_product_image",
            "p43j_product_option",
            "p43j_product_option_value",
            "p43j_product_recurring",
            "p43j_product_related",
            "p43j_product_related_article",
            "p43j_product_related_mn",
            "p43j_product_related_wb",
            "p43j_product_reward",
            "p43j_product_special",
            "p43j_product_tab",
            "p43j_product_tab_desc",
            "p43j_product_to_benefit",
            "p43j_product_to_category",
            "p43j_product_to_download",
            "p43j_product_to_layout",
            "p43j_product_to_sticker",
            "p43j_product_to_store",
        ]
    else:
        return [
            "p43j_product_to_category",
            "p43j_product_to_download",
            "p43j_product_to_layout",
            "p43j_product_to_sticker",
            "p43j_product_to_store",
        ]


def decode_val(value: str) -> str:
    value = value.replace("ÊÏ", "КП")
    value = value.replace("Ïàðôþìåðèÿ", "Парфюмерия")
    value = value.replace("Êîëãîòêè è Áåëü¸", "Колготки и Бельё")
    value = value.replace("Êîñìåòèêà", "Косметика")
    return value
